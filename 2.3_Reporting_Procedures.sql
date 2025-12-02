USE TrelloDB;
DELIMITER //
DROP PROCEDURE IF EXISTS SP_Report_BoardDetails;

CREATE PROCEDURE SP_Report_BoardDetails(
    IN p_BoardID INT,
    IN p_IsCompleted BOOLEAN
)
BEGIN
    SELECT 
        L.Title AS ListName,
        C.CardID,
        C.Title AS TaskName,
        C.Priority,
        C.DueDate,
        IFNULL(GROUP_CONCAT(U.LastName SEPARATOR ', '), 'Unassigned') AS Assignees, -- 5
        FUNC_Calculate_Completion_Rate(C.CardID) AS ProgressPercent, -- 6
        C.IsCompleted
    FROM 
        Card C
    JOIN 
        Lists L ON C.ListID = L.ListID
    LEFT JOIN 
        Card_Member CM ON C.CardID = CM.CardID
    LEFT JOIN 
        Users U ON CM.UserID = U.UserID
    WHERE 
        L.BoardID = p_BoardID 
        AND (p_IsCompleted IS NULL OR C.IsCompleted = p_IsCompleted)
    GROUP BY 
        C.CardID, C.Title, C.Priority, C.DueDate, L.Title, L.Position, C.IsCompleted
    ORDER BY 
        L.Position ASC,
        C.IsCompleted ASC,
        C.Priority ASC;
END //

DROP PROCEDURE IF EXISTS SP_Report_UserWorkload;

CREATE PROCEDURE SP_Report_UserWorkload(
    IN p_MinTaskThreshold INT
)
BEGIN
    SELECT 
        U.UserID,
        CONCAT(U.FirstName, ' ', U.LastName) AS FullName,
        U.Email,
        COUNT(C.CardID) AS ActiveTaskCount
    FROM 
        Users U
    JOIN 
        Card_Member CM ON U.UserID = CM.UserID
    JOIN 
        Card C ON CM.CardID = C.CardID
    WHERE 
        C.IsCompleted = FALSE
    GROUP BY 
        U.UserID, U.FirstName, U.LastName, U.Email
    HAVING 
        COUNT(C.CardID) >= p_MinTaskThreshold
    ORDER BY 
        ActiveTaskCount DESC;
END //

DELIMITER ;